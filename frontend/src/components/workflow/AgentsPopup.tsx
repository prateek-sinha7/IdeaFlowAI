"use client";

import { motion, AnimatePresence } from "motion/react";
import { X, BookOpen, Zap, Trash2, Plus } from "lucide-react";
import { AgentLibrary } from "./AgentLibrary";
import { useState } from "react";
import type { AgentDef, WorkflowType } from "@/types/index";

interface AgentsPopupProps {
  isOpen: boolean;
  onClose: () => void;
  agents: AgentDef[];
  pipelineType: WorkflowType;
  onAddAgent?: (agent: AgentDef) => void;
  onRemoveAgent?: (agentId: string) => void;
}

/**
 * Full-screen popup showing all agents in the pipeline.
 * Supports adding agents from the library and removing existing ones.
 */
export function AgentsPopup({ isOpen, onClose, agents, pipelineType, onAddAgent, onRemoveAgent }: AgentsPopupProps) {
  const [libraryOpen, setLibraryOpen] = useState(false);

  const totalDuration = agents.reduce((sum, a) => sum + a.estimated_duration, 0);

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-6"
        >
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.25 }}
            className="relative w-full max-w-2xl max-h-[80vh] rounded-2xl border border-white/10 bg-[#0a0f1a] shadow-2xl shadow-black/50 overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/8">
              <div>
                <h2 className="text-sm font-semibold text-white">Agent Pipeline</h2>
                <p className="text-[11px] text-white/40 mt-0.5">
                  {agents.length} agents • ~{Math.ceil(totalDuration / 60)} min estimated
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setLibraryOpen(true)}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium text-white/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all"
                >
                  <Plus className="h-3 w-3" />
                  Add Agent
                </button>
                <button
                  onClick={() => setLibraryOpen(true)}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium text-white/60 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 transition-all"
                >
                  <BookOpen className="h-3 w-3" />
                  Browse Library
                </button>
                <button
                  onClick={onClose}
                  className="flex items-center justify-center rounded-lg p-2 text-white/40 hover:text-white hover:bg-white/5 transition-all"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Agent List */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <div className="space-y-2">
                {agents.map((agent, idx) => (
                  <motion.div
                    key={agent.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.03 }}
                    className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[0.02] hover:bg-white/[0.04] px-4 py-3 transition-all group"
                  >
                    <span className="text-[11px] text-white/30 w-5 text-center font-mono">{idx + 1}</span>
                    <span className="text-base flex-shrink-0">{agent.icon}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-[12px] font-medium text-white/90">{agent.name}</p>
                      <p className="text-[10px] text-white/40 truncate">{agent.description}</p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="text-[9px] text-white/30 bg-white/5 rounded px-1.5 py-0.5">{agent.role}</span>
                      <span className="text-[9px] text-white/25 flex items-center gap-0.5">
                        <Zap className="h-2.5 w-2.5" />
                        ~{agent.estimated_duration}s
                      </span>
                      {onRemoveAgent && (
                        <button
                          onClick={() => onRemoveAgent(agent.id)}
                          className="opacity-0 group-hover:opacity-100 p-1 rounded text-white/30 hover:text-red-400 hover:bg-red-500/10 transition-all"
                          title="Remove agent"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-white/8 flex items-center justify-between">
              <p className="text-[10px] text-white/30">
                Agents execute sequentially. Each receives context from previous agents.
              </p>
              <button
                onClick={onClose}
                className="rounded-lg bg-white/10 hover:bg-white/15 px-4 py-2 text-xs font-medium text-white transition-all"
              >
                Done
              </button>
            </div>
          </motion.div>

          {/* Agent Library (nested) — passes onAddAgent to add from library */}
          <AgentLibrary
            isOpen={libraryOpen}
            onClose={() => setLibraryOpen(false)}
            onAddAgent={onAddAgent}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
