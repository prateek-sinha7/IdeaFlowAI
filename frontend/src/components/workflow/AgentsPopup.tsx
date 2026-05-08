"use client";

import { useCallback, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, Zap, Trash2, Plus, GripVertical, Lock, Shield, Bot } from "lucide-react";
import { AgentLibrary } from "./AgentLibrary";
import type { AgentDef, WorkflowType } from "@/types/index";

interface AgentsPopupProps {
  isOpen: boolean;
  onClose: () => void;
  agents: AgentDef[];
  pipelineType: WorkflowType;
  onAddAgent?: (agent: AgentDef) => void;
  onRemoveAgent?: (agentId: string) => void;
  onReorder?: (agents: AgentDef[]) => void;
  canAddMore?: boolean;
}

// Agents that are locked (cannot be removed or moved) — first and last of each pipeline
const LOCKED_AGENT_IDS = new Set([
  // User Stories
  "domain-analyst", "backlog-compiler",
  // PPT
  "audience-analyst", "export-formatter",
  // Prototype
  "requirements-analyst", "prototype-finalizer",
  // App Builder
  "material-analyzer", "app-assembler",
  // Reverse Engineer
  "repo-scanner", "documentation-generator",
]);

// Agents that are required (cannot be removed but can be reordered among themselves)
const REQUIRED_AGENT_IDS = new Set([
  // User Stories
  "epic-architect", "story-estimator", "nfr-specialist", "backlog-reviewer",
  // PPT
  "slide-architect", "data-enricher", "speaker-notes-writer", "slide-polisher",
  // Prototype
  "html-prototype-builder", "prototype-polisher",
  // App Builder
  "app-code-generator", "app-infra-generator",
  // Reverse Engineer
  "deep-analyzer", "modernization-planner",
]);

type AgentRole = "locked" | "required" | "optional";

function getAgentRole(agentId: string): AgentRole {
  if (LOCKED_AGENT_IDS.has(agentId)) return "locked";
  if (REQUIRED_AGENT_IDS.has(agentId)) return "required";
  return "optional";
}

function getRoleBadge(role: AgentRole) {
  switch (role) {
    case "locked": return { label: "Core", color: "bg-slate-100 text-slate-600 border-slate-200", icon: Lock };
    case "required": return { label: "Required", color: "bg-blue-50 text-blue-600 border-blue-200", icon: Shield };
    case "optional": return { label: "Optional", color: "bg-amber-50 text-amber-600 border-amber-200", icon: Plus };
  }
}

export function AgentsPopup({ isOpen, onClose, agents, pipelineType, onAddAgent, onRemoveAgent, onReorder, canAddMore = true }: AgentsPopupProps) {
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  const totalDuration = agents.reduce((sum, a) => sum + a.estimated_duration, 0);

  const handleDragStart = useCallback((idx: number) => {
    const role = getAgentRole(agents[idx].id);
    if (role === "locked") return; // Can't drag locked agents
    setDraggedIdx(idx);
  }, [agents]);

  const handleDragOver = useCallback((e: React.DragEvent, idx: number) => {
    e.preventDefault();
    // Can't drop on locked positions (first or last)
    const role = getAgentRole(agents[idx].id);
    if (role === "locked") return;
    setDragOverIdx(idx);
  }, [agents]);

  const handleDragEnd = useCallback(() => { setDraggedIdx(null); setDragOverIdx(null); }, []);

  const handleDrop = useCallback((idx: number) => {
    if (draggedIdx === null || draggedIdx === idx) { setDraggedIdx(null); setDragOverIdx(null); return; }
    // Don't allow dropping on locked positions
    const targetRole = getAgentRole(agents[idx].id);
    if (targetRole === "locked") { setDraggedIdx(null); setDragOverIdx(null); return; }

    const updated = [...agents];
    const [moved] = updated.splice(draggedIdx, 1);
    updated.splice(idx, 0, moved);
    onReorder?.(updated);
    setDraggedIdx(null);
    setDragOverIdx(null);
  }, [draggedIdx, agents, onReorder]);

  const handleRemove = useCallback((agentId: string) => {
    const role = getAgentRole(agentId);
    if (role === "locked" || role === "required") return; // Can't remove locked or required
    onRemoveAgent?.(agentId);
  }, [onRemoveAgent]);

  // Find insertion point (before the last locked agent)
  const lastLockedIdx = agents.length - 1;
  const canInsert = agents.length > 0;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-6">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose} />
          <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} transition={{ duration: 0.25 }}
            className="relative w-full sm:max-w-2xl max-h-[90vh] sm:max-h-[80vh] rounded-t-2xl sm:rounded-2xl border border-[#e8e6dc] bg-white shadow-2xl shadow-black/10 overflow-hidden flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#e8e6dc]">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-semibold text-[#141413]">Autonomous Pipeline</h2>
                  <span className="flex items-center gap-1 text-[9px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">
                    <Bot className="h-2.5 w-2.5" /> Auto
                  </span>
                </div>
                <p className="text-[11px] text-[#87867f] mt-0.5">{agents.length} agents • ~{Math.ceil(totalDuration / 60)} min • Runs autonomously once started</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => canAddMore && setLibraryOpen(true)}
                  disabled={!canAddMore}
                  className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium border transition-all ${
                    canAddMore
                      ? "text-[#5e5d59] hover:text-[#141413] bg-[#faf9f5] hover:bg-[#f0eee6] border-[#e8e6dc]"
                      : "text-[#c9c8c3] bg-[#faf9f5] border-[#e8e6dc] cursor-not-allowed"
                  }`}
                  title={canAddMore ? "Add an optional agent" : "Maximum 2 optional agents allowed"}
                >
                  <Plus className="h-3 w-3" /> {canAddMore ? "Add Agent" : "Limit Reached (2 max)"}
                </button>
                <button onClick={onClose} className="flex items-center justify-center rounded-lg p-2 text-[#87867f] hover:text-[#141413] hover:bg-[#f5f4ed] transition-all">
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Legend */}
            <div className="px-6 py-2 border-b border-[#f0eee6] flex items-center gap-3">
              <span className="flex items-center gap-1 text-[9px] text-[#87867f]"><Lock className="h-2.5 w-2.5" /> Core = locked</span>
              <span className="flex items-center gap-1 text-[9px] text-[#87867f]"><Shield className="h-2.5 w-2.5" /> Required = can reorder</span>
              <span className="flex items-center gap-1 text-[9px] text-[#87867f]"><Plus className="h-2.5 w-2.5" /> Optional = can remove</span>
            </div>

            {/* Agent List */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <div className="space-y-1.5">
                {agents.map((agent, idx) => {
                  const role = getAgentRole(agent.id);
                  const badge = getRoleBadge(role);
                  const BadgeIcon = badge.icon;
                  const isLocked = role === "locked";
                  const canDrag = !isLocked;
                  const canDelete = role === "optional";

                  return (
                    <div
                      key={agent.id}
                      draggable={canDrag}
                      onDragStart={() => canDrag && handleDragStart(idx)}
                      onDragOver={(e) => handleDragOver(e, idx)}
                      onDrop={() => handleDrop(idx)}
                      onDragEnd={handleDragEnd}
                      className="relative"
                    >
                      {/* Drop indicator */}
                      {dragOverIdx === idx && draggedIdx !== null && draggedIdx !== idx && (
                        <div className="absolute -top-0.5 left-0 right-0 h-0.5 bg-[#c96442] rounded-full z-10" />
                      )}
                      <div className={`flex items-center gap-2 rounded-xl border px-3 py-2.5 transition-all group ${
                        isLocked ? "border-slate-200 bg-slate-50" :
                        draggedIdx === idx ? "opacity-40 scale-[0.98] border-[#e8e6dc] bg-[#faf9f5]" :
                        "border-[#e8e6dc] bg-[#faf9f5] hover:bg-[#f0eee6]"
                      }`}>
                        {/* Drag handle or lock */}
                        {isLocked ? (
                          <Lock className="h-3 w-3 text-slate-400 flex-shrink-0" />
                        ) : (
                          <GripVertical className="h-3.5 w-3.5 text-[#87867f] cursor-grab active:cursor-grabbing flex-shrink-0" />
                        )}
                        <span className="text-[11px] text-[#87867f] w-4 text-center font-mono flex-shrink-0">{idx + 1}</span>
                        <span className="text-base flex-shrink-0">{agent.icon}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <p className={`text-[11px] font-medium ${isLocked ? "text-slate-600" : "text-[#141413]"}`}>{agent.name}</p>
                            <span className={`text-[7px] font-semibold px-1.5 py-0.5 rounded-full border ${badge.color}`}>
                              {badge.label}
                            </span>
                          </div>
                          <p className="text-[9px] text-[#87867f] truncate">{agent.role}</p>
                        </div>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          <span className="text-[8px] text-[#87867f] flex items-center gap-0.5"><Zap className="h-2 w-2" />~{agent.estimated_duration}s</span>
                          {canDelete && (
                            <button onClick={() => handleRemove(agent.id)} className="opacity-0 group-hover:opacity-100 p-1 rounded text-[#87867f] hover:text-red-500 hover:bg-red-50 transition-all" title="Remove">
                              <Trash2 className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Connector line between agents */}
                      {idx < agents.length - 1 && (
                        <div className="flex justify-center py-0.5">
                          <div className="w-px h-2 bg-[#e8e6dc]" />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-[#e8e6dc] flex items-center justify-between">
              <p className="text-[10px] text-[#87867f]">Agents execute sequentially, top → bottom</p>
              <button onClick={onClose} className="rounded-lg bg-[#c96442] hover:bg-[#b5573a] px-4 py-2 text-xs font-medium text-white transition-all shadow-sm">
                Done
              </button>
            </div>
          </motion.div>

          <AgentLibrary isOpen={libraryOpen} onClose={() => setLibraryOpen(false)} onAddAgent={onAddAgent} currentPipelineType={pipelineType} canAddMore={canAddMore} existingAgentIds={agents.map((a) => a.id)} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
