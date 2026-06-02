"use client";

import type { PipelineRunState } from "@/types/index";

interface DagEdge {
  from: string;
  to: string;
  artifact_type: string;
}

interface UnresolvedEdge {
  consuming_agent_id: string;
  artifact_type: string;
}

interface DependencyGraphProps {
  /** Resolved producer→consumer edges from the workflow_validated event */
  dagEdges?: DagEdge[];
  /** Unsatisfied edges — rendered visually distinct (dashed/red) */
  unresolvedEdges?: UnresolvedEdge[];
  /** Agent list for node labels */
  agents?: PipelineRunState["agents"];
}

/**
 * T065 — Visual Dependency Graph (FR-005).
 *
 * Renders the computed Workflow DAG:
 * - One node per agent
 * - One directed edge per resolved producer→consumer Artifact_Type relationship
 * - Unsatisfied edges visually distinct (dashed, red) from satisfied edges (solid, green)
 *
 * Mounted within the existing agent-detail presentation surface (below the agent list
 * in AgentProgressPanel) when dagEdges is non-empty.
 *
 * Uses a simple left-to-right layout without an external graph library.
 */
export function DependencyGraph({ dagEdges, unresolvedEdges, agents }: DependencyGraphProps) {
  if (!dagEdges || dagEdges.length === 0) return null;

  // Build a set of all agent IDs that appear in edges
  const agentIds = new Set<string>();
  dagEdges.forEach(e => { agentIds.add(e.from); agentIds.add(e.to); });
  unresolvedEdges?.forEach(e => agentIds.add(e.consuming_agent_id));

  // Build agent name map from the agents prop
  const nameMap: Record<string, string> = {};
  agents?.forEach(a => { nameMap[a.id] = a.name; });

  // Group edges by from_agent for display
  const edgesByFrom: Record<string, DagEdge[]> = {};
  dagEdges.forEach(e => {
    if (!edgesByFrom[e.from]) edgesByFrom[e.from] = [];
    edgesByFrom[e.from].push(e);
  });

  return (
    <div className="px-3 py-3 border-t border-gray-100">
      <p className="text-[9px] font-semibold text-gray-400 uppercase tracking-widest mb-2">
        Workflow DAG
      </p>
      <div className="space-y-1.5">
        {dagEdges.map((edge, i) => (
          <div key={i} className="flex items-center gap-1.5 text-[10px]">
            <span className="bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded text-[9px] font-mono truncate max-w-[80px]">
              {nameMap[edge.from] || edge.from}
            </span>
            <div className="flex items-center gap-0.5 flex-shrink-0">
              <div className="w-4 h-px bg-emerald-400" />
              <div className="w-0 h-0 border-t-[3px] border-t-transparent border-b-[3px] border-b-transparent border-l-[5px] border-l-emerald-400" />
            </div>
            <span className="text-[8px] text-emerald-600 bg-emerald-50 px-1 py-0.5 rounded font-mono truncate max-w-[60px]">
              {edge.artifact_type}
            </span>
            <div className="flex items-center gap-0.5 flex-shrink-0">
              <div className="w-4 h-px bg-emerald-400" />
              <div className="w-0 h-0 border-t-[3px] border-t-transparent border-b-[3px] border-b-transparent border-l-[5px] border-l-emerald-400" />
            </div>
            <span className="bg-gray-100 text-gray-700 px-1.5 py-0.5 rounded text-[9px] font-mono truncate max-w-[80px]">
              {nameMap[edge.to] || edge.to}
            </span>
          </div>
        ))}
        {unresolvedEdges && unresolvedEdges.length > 0 && (
          <>
            <p className="text-[9px] font-semibold text-red-400 uppercase tracking-widest mt-2 mb-1">
              Unsatisfied ({unresolvedEdges.length})
            </p>
            {unresolvedEdges.map((edge, i) => (
              <div key={i} className="flex items-center gap-1.5 text-[10px]">
                <span className="bg-red-50 text-red-600 px-1.5 py-0.5 rounded text-[9px] font-mono truncate max-w-[80px]">
                  {nameMap[edge.consuming_agent_id] || edge.consuming_agent_id}
                </span>
                <div className="flex items-center gap-0.5 flex-shrink-0">
                  {/* Dashed line for unsatisfied */}
                  <svg width="20" height="8" viewBox="0 0 20 8">
                    <line x1="0" y1="4" x2="14" y2="4" stroke="#ef4444" strokeWidth="1.5" strokeDasharray="3,2" />
                    <polygon points="14,1 20,4 14,7" fill="#ef4444" />
                  </svg>
                </div>
                <span className="text-[8px] text-red-500 bg-red-50 px-1 py-0.5 rounded font-mono truncate max-w-[60px]">
                  {edge.artifact_type}
                </span>
                <span className="text-[9px] text-red-400 italic">missing</span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
