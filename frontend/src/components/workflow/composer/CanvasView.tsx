"use client";

import { useState } from "react";
import { Plus, Minus, Maximize, Save, Play } from "lucide-react";
import { CanvasNode } from "./CanvasNode";
import { CanvasConfigRail } from "./CanvasConfigRail";
import type { SelectionsMap, StepSelection } from "../AgentsPopup";
import type { AgentDef, WorkflowType } from "@/types/index";

// ── Hand-rolled layout constants (px, shared by the nodes + the SVG edge layer;
//    both live in the same `.stage` coordinate space so they align — D-04). ──────
const NODE_W = 178;
const NODE_GAP = 54;
const START_X = 170;
const NODE_Y = 240;
const PORT_Y = 306; // vertical centre of the node ports (and every edge)
const BRIEF_X = 20;
const BRIEF_Y = 282;
const BRIEF_W = 118;
const ARROW_INSET = 8; // stop the edge just short of the target port

const nodeLeft = (i: number) => START_X + i * (NODE_W + NODE_GAP);

/** A smooth horizontal cubic bezier between two points on the same baseline. */
function edgePath(sx: number, sy: number, ex: number, ey: number): string {
  const dx = Math.max(20, (ex - sx) * 0.5);
  return `M ${sx} ${sy} C ${sx + dx} ${sy}, ${ex - dx} ${ey}, ${ex} ${ey}`;
}

/**
 * 41-05 — the Composer's CANVAS view: a HAND-ROLLED node-graph visual designer
 * (D-04 / CMPUI-03), design-matched to the APPROVED PROPOSAL
 * `composer-canvas-proposal.html` (ND-AJ — a design-match gate, not a `.dc.html`
 * mock-fidelity gate).
 *
 * An `<svg>` edge layer (bezier `path`s + grey/brand arrow markers) sits UNDER
 * absolute-positioned agent node divs in a left→right sequential chain, preceded
 * by a dark Brief trigger pill. Clicking a node selects it (brand ring + the edge
 * INTO it tinted brand) and the right config rail binds that node's Model /
 * Overrides / Custom-prompt to the shared `SelectionsMap` (via the REUSED
 * AdvancedExpander + AgentPromptSection). `+` insert affordances on the edges and
 * at the chain end call the SAME add-agent path as the Simple view; a node's
 * remove drops it from `pipelineAgents`. A docked Run summary (agents ·
 * review-gates · live est. duration · declared caps — NO est. cost, ND-AG) sits
 * beneath the rail. Bound to the SAME shared data model as the Simple view — NO
 * graph/dnd library (hand-rolled SVG + absolute divs).
 */
export function CanvasView({
  pipelineAgents,
  selections,
  pipelineType,
  onSelection,
  onRemoveAgent,
  onAddAgent,
  canAddMore,
  gateCount,
  strategy,
  estDurationLabel,
  declaredCapabilities,
  onSaveToCatalogue,
  onRunOnce,
}: {
  pipelineAgents: AgentDef[];
  selections: SelectionsMap;
  pipelineType: WorkflowType;
  onSelection: (agentId: string, sel: StepSelection | undefined) => void;
  onRemoveAgent: (id: string) => void;
  onAddAgent: () => void;
  canAddMore: boolean;
  gateCount: number;
  strategy: string;
  estDurationLabel: string;
  declaredCapabilities: string[];
  onSaveToCatalogue: () => void;
  onRunOnce?: () => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(
    pipelineAgents[0]?.id ?? null,
  );
  const [zoom, setZoom] = useState(1);

  // Effective selection (fall back to the first node if the selected one was
  // removed, so the rail always reflects an existing node).
  const foundIndex = pipelineAgents.findIndex((a) => a.id === selectedId);
  const selIndex =
    foundIndex >= 0 ? foundIndex : pipelineAgents.length > 0 ? 0 : -1;
  const selAgent = selIndex >= 0 ? pipelineAgents[selIndex] : null;

  // Edge list: Brief→node0, then node[i-1]→node[i]. Edge `j` targets node `j`
  // (so it tints brand when node `j` is selected).
  const edges = pipelineAgents.map((_, i) => {
    const sx = i === 0 ? BRIEF_X + BRIEF_W : nodeLeft(i - 1) + NODE_W;
    const ex = nodeLeft(i) - ARROW_INSET;
    return { key: i, sx, ex, active: i === selIndex };
  });

  // Inter-node insert affordances (between consecutive nodes) + a chain-end add.
  const inserts = pipelineAgents.slice(1).map((_, k) => {
    const i = k; // between node i and node i+1
    return { key: `ins-${i}`, x: (nodeLeft(i) + NODE_W + nodeLeft(i + 1)) / 2 };
  });
  const chainEndX =
    pipelineAgents.length > 0
      ? nodeLeft(pipelineAgents.length - 1) + NODE_W + 34
      : BRIEF_X + BRIEF_W + 34;

  return (
    <div data-testid="canvas-view" className="flex h-full min-h-0">
      {/* ── Canvas (dot-grid) ─────────────────────────────────────────────── */}
      <div
        className="relative flex-1 overflow-hidden"
        style={{
          background:
            "radial-gradient(circle at 1px 1px, var(--line-faint) 1.2px, transparent 0) 0 0 / 22px 22px, var(--surface-paper)",
        }}
      >
        {/* hint */}
        <div className="absolute left-[22px] top-4 z-[4] flex items-center gap-3.5 font-sans text-[11.5px] text-ink-300">
          <span>
            <b className="font-semibold text-ink-500">Click</b> a node to configure
          </span>
          <span>
            <b className="font-semibold text-ink-500">+</b> to insert an agent
          </span>
        </div>

        {/* stage — the nodes + the SVG edge layer share this coordinate space */}
        <div
          className="absolute inset-0"
          style={{ transform: `scale(${zoom})`, transformOrigin: "0 0" }}
        >
          {/* edges UNDER the nodes */}
          <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible">
            <defs>
              <marker
                id="arw"
                markerWidth="9"
                markerHeight="9"
                refX="6.5"
                refY="4.5"
                orient="auto"
              >
                <path d="M1 1 L7 4.5 L1 8 Z" fill="var(--ink-300)" />
              </marker>
              <marker
                id="arwb"
                markerWidth="9"
                markerHeight="9"
                refX="6.5"
                refY="4.5"
                orient="auto"
              >
                <path d="M1 1 L7 4.5 L1 8 Z" fill="var(--brand)" />
              </marker>
            </defs>
            {edges.map((e) => (
              <path
                key={e.key}
                data-testid="canvas-edge"
                data-active={e.active ? "true" : "false"}
                d={edgePath(e.sx, PORT_Y, e.ex, PORT_Y)}
                fill="none"
                stroke={e.active ? "var(--brand)" : "var(--line-faint)"}
                strokeWidth={e.active ? 2 : 1.75}
                markerEnd={`url(#${e.active ? "arwb" : "arw"})`}
              />
            ))}
          </svg>

          {/* Brief trigger pill (dark) */}
          <div
            data-testid="canvas-brief"
            style={{ left: BRIEF_X, top: BRIEF_Y, width: BRIEF_W }}
            className="absolute z-[3] rounded-[11px] bg-surface-near-black px-3 py-2.5 shadow-[0_2px_8px_rgba(17,17,20,0.12)]"
          >
            <div className="font-sans text-[9px] font-bold uppercase tracking-[0.12em] text-brand-on-dark">
              Brief
            </div>
            <div className="mt-0.5 font-sans text-[12px] font-semibold text-surface-white">
              What to build
            </div>
            <div className="mt-0.5 font-serif text-[10px] text-ink-300">
              the run input
            </div>
            <span className="absolute top-1/2 -right-[6px] h-[11px] w-[11px] -translate-y-1/2 rounded-full border-2 border-ink-700 bg-surface-near-black" />
          </div>

          {/* agent nodes */}
          {pipelineAgents.map((agent, i) => (
            <CanvasNode
              key={agent.id}
              agent={agent}
              pipelineType={pipelineType}
              selection={selections[agent.id]}
              selected={i === selIndex}
              onSelect={() => setSelectedId(agent.id)}
              onRemove={() => onRemoveAgent(agent.id)}
              left={nodeLeft(i)}
              top={NODE_Y}
              width={NODE_W}
            />
          ))}

          {/* insert affordances ON the edges (between consecutive nodes) */}
          {inserts.map((ins) => (
            <button
              key={ins.key}
              type="button"
              aria-label="Add agent"
              title="Insert an agent"
              disabled={!canAddMore}
              onClick={onAddAgent}
              style={{ left: ins.x, top: PORT_Y }}
              className="absolute z-[5] grid h-[22px] w-[22px] -translate-x-1/2 -translate-y-1/2 place-items-center rounded-[7px] border border-line-control bg-surface-card text-[15px] leading-none text-ink-500 shadow-[0_1px_3px_rgba(17,17,20,0.08)] enabled:hover:border-brand enabled:hover:text-brand disabled:opacity-40"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          ))}

          {/* add-agent affordance at the chain end */}
          <button
            type="button"
            aria-label="Add agent"
            title="Add an agent"
            disabled={!canAddMore}
            onClick={onAddAgent}
            style={{ left: chainEndX, top: PORT_Y }}
            className="absolute z-[5] grid h-[30px] w-[30px] -translate-x-1/2 -translate-y-1/2 place-items-center rounded-[8px] border border-line-control bg-surface-card text-ink-500 shadow-[0_1px_3px_rgba(17,17,20,0.08)] enabled:hover:border-brand enabled:hover:text-brand disabled:opacity-40"
          >
            <Plus className="h-[18px] w-[18px]" />
          </button>
        </div>

        {/* zoom / Fit controls */}
        <div className="absolute bottom-5 left-[22px] z-[6] flex gap-2">
          <div className="flex overflow-hidden rounded-[10px] border border-line-control bg-surface-card shadow-[0_1px_3px_rgba(17,17,20,0.06)]">
            <button
              type="button"
              aria-label="Zoom out"
              onClick={() => setZoom((z) => Math.max(0.4, Math.round((z - 0.1) * 10) / 10))}
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
            onClick={() => setZoom(1)}
            className="flex items-center gap-1.5 rounded-[10px] border border-line-control bg-surface-card px-3 py-2 font-sans text-[12px] font-semibold text-ink-500 shadow-[0_1px_3px_rgba(17,17,20,0.06)] hover:text-ink-900"
          >
            <Maximize className="h-3.5 w-3.5" />
            Fit
          </button>
        </div>
      </div>

      {/* ── Right rail: selected-node config + docked Run summary ──────────── */}
      <aside className="flex w-[344px] flex-none flex-col border-l border-line-divider bg-surface-card">
        <CanvasConfigRail
          agent={selAgent}
          index={selIndex}
          total={pipelineAgents.length}
          selection={selAgent ? selections[selAgent.id] : undefined}
          onSelection={onSelection}
        />

        {/* docked Run summary — the proposal's 2×2 stat-card grid (ND-AG: the
            Est-cost card is OMITTED). Uses the SAME computed summary data the
            Simple view passes (agent/review-gate counts, live est. duration,
            declared-cap chips) — no forked counting logic. */}
        <div
          data-testid="canvas-run-summary"
          className="flex-none border-t border-line-divider bg-surface-warm px-[18px] py-4"
        >
          <div className="mb-3 flex items-baseline justify-between">
            <b className="font-sans text-[12.5px] font-semibold text-ink-900">
              Run summary
            </b>
            <span className="font-serif text-[11px] text-ink-300">{strategy}</span>
          </div>

          <div className="mb-3 grid grid-cols-2 gap-2">
            <div className="rounded-[9px] border border-line-border bg-surface-card px-2.5 py-2.5">
              <div className="font-sans text-[16px] font-bold tabular-nums leading-none tracking-[-0.02em] text-ink-900">
                {pipelineAgents.length}
              </div>
              <div className="mt-1 font-sans text-[10px] uppercase tracking-[0.06em] text-ink-300">
                Agents
              </div>
            </div>
            <div className="rounded-[9px] border border-line-border bg-surface-card px-2.5 py-2.5">
              <div className="font-sans text-[16px] font-bold tabular-nums leading-none tracking-[-0.02em] text-ink-900">
                {gateCount}
              </div>
              <div className="mt-1 font-sans text-[10px] uppercase tracking-[0.06em] text-ink-300">
                Review gate
              </div>
            </div>
            <div className="rounded-[9px] border border-line-border bg-surface-card px-2.5 py-2.5">
              <div className="font-sans text-[16px] font-bold tabular-nums leading-none tracking-[-0.02em] text-ink-900">
                {estDurationLabel}
              </div>
              <div className="mt-1 font-sans text-[10px] uppercase tracking-[0.06em] text-ink-300">
                Est. duration
              </div>
            </div>
            {/* 4th grid cell (Est. cost) OMITTED — ND-AG. */}
          </div>

          {/* declared-capability chips */}
          {declaredCapabilities.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {declaredCapabilities.map((c) => (
                <span
                  key={c}
                  className="rounded-[6px] border border-brand-border bg-brand-fill px-[7px] py-[3px] font-sans text-[10.5px] font-semibold text-brand"
                >
                  {c}
                </span>
              ))}
            </div>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={onSaveToCatalogue}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-[10px] border border-line-control bg-surface-card px-3 py-2.5 font-sans text-[12.5px] font-semibold text-ink-700 transition-colors hover:border-line-faint"
            >
              <Save className="h-3.5 w-3.5" />
              Save to catalogue
            </button>
            <button
              type="button"
              onClick={onRunOnce}
              disabled={!onRunOnce}
              title="Run wiring lands in 41-06"
              className="flex flex-1 items-center justify-center gap-1.5 rounded-[10px] bg-brand px-3 py-2.5 font-sans text-[12.5px] font-semibold text-surface-white transition-colors enabled:hover:bg-brand-pressed disabled:opacity-60"
            >
              <Play className="h-3.5 w-3.5" />
              Run once
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}
