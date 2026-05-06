"use client";

import { useCallback, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, BookOpen, Zap, Trash2, Plus, GripVertical } from "lucide-react";
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
}

export function AgentsPopup({ isOpen, onClose, agents, pipelineType, onAddAgent, onRemoveAgent, onReorder }: AgentsPopupProps) {
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null);

  const totalDuration = agents.reduce((sum, a) => sum + a.estimated_duration, 0);

  const handleDragStart = useCallback((idx: number) => { setDraggedIdx(idx); }, []);
  const handleDragOver = useCallback((e: React.DragEvent, idx: number) => { e.preventDefault(); setDragOverIdx(idx); }, []);
  const handleDragEnd = useCallback(() => { setDraggedIdx(null); setDragOverIdx(null); }, []);
  const handleDrop = useCallback((idx: number) => {
    if (draggedIdx === null || draggedIdx === idx) { setDraggedIdx(null); setDragOverIdx(null); return; }
    const updated = [...agents];
    const [moved] = updated.splice(draggedIdx, 1);
    updated.splice(idx, 0, moved);
    onReorder?.(updated);
    setDraggedIdx(null);
    setDragOverIdx(null);
  }, [draggedIdx, agents, onReorder]);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose} />
          <motion.div initial={{ opacity: 0, scale: 0.95, y: 20 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95, y: 20 }} transition={{ duration: 0.25 }}
            className="relative w-full max-w-2xl max-h-[80vh] rounded-2xl border border-[#e8e6dc] bg-white shadow-2xl shadow-black/10 overflow-hidden flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#e8e6dc]">
              <div>
                <h2 className="text-sm font-semibold text-[#141413]">Agent Pipeline</h2>
                <p className="text-[11px] text-[#87867f] mt-0.5">{agents.length} agents • ~{Math.ceil(totalDuration / 60)} min estimated • Drag to reorder</p>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => setLibraryOpen(true)} className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium text-[#5e5d59] hover:text-[#141413] bg-[#faf9f5] hover:bg-[#f0eee6] border border-[#e8e6dc] transition-all">
                  <Plus className="h-3 w-3" /> Add Agent
                </button>
                <button onClick={onClose} className="flex items-center justify-center rounded-lg p-2 text-[#87867f] hover:text-[#141413] hover:bg-[#f5f4ed] transition-all">
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Agent List with drag-and-drop */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <div className="space-y-1.5">
                {agents.map((agent, idx) => (
                  <div
                    key={agent.id}
                    draggable
                    onDragStart={() => handleDragStart(idx)}
                    onDragOver={(e) => handleDragOver(e, idx)}
                    onDrop={() => handleDrop(idx)}
                    onDragEnd={handleDragEnd}
                    className="relative"
                  >
                    {/* Drop indicator line */}
                    {dragOverIdx === idx && draggedIdx !== null && draggedIdx !== idx && (
                      <div className="absolute -top-0.5 left-0 right-0 h-0.5 bg-[#c96442] rounded-full z-10" />
                    )}
                    <div className={`flex items-center gap-2 rounded-xl border border-[#e8e6dc] bg-[#faf9f5] hover:bg-[#f0eee6] px-3 py-2.5 transition-all group ${
                      draggedIdx === idx ? "opacity-40 scale-[0.98]" : ""
                    }`}>
                      {/* Drag handle */}
                      <GripVertical className="h-3.5 w-3.5 text-[#87867f] cursor-grab active:cursor-grabbing flex-shrink-0" />
                      <span className="text-[11px] text-[#87867f] w-4 text-center font-mono flex-shrink-0">{idx + 1}</span>
                      <span className="text-base flex-shrink-0">{agent.icon}</span>
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] font-medium text-[#141413]">{agent.name}</p>
                        <p className="text-[9px] text-[#87867f] truncate">{agent.description}</p>
                      </div>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <span className="text-[8px] text-[#87867f] flex items-center gap-0.5"><Zap className="h-2 w-2" />~{agent.estimated_duration}s</span>
                        {onRemoveAgent && (
                          <button onClick={() => onRemoveAgent(agent.id)} className="opacity-0 group-hover:opacity-100 p-1 rounded text-[#87867f] hover:text-red-500 hover:bg-red-50 transition-all" title="Remove">
                            <Trash2 className="h-3 w-3" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-[#e8e6dc] flex items-center justify-between">
              <p className="text-[10px] text-[#87867f]">Drag ⋮⋮ to reorder • Agents execute top to bottom</p>
              <button onClick={onClose} className="rounded-lg bg-[#c96442] hover:bg-[#b5573a] px-4 py-2 text-xs font-medium text-white transition-all shadow-sm">
                Done
              </button>
            </div>
          </motion.div>

          <AgentLibrary isOpen={libraryOpen} onClose={() => setLibraryOpen(false)} onAddAgent={onAddAgent} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
