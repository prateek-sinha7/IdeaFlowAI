"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, Search, Plus, Zap, FileText, Presentation, Layout, Layers } from "lucide-react";
import type { AgentDef } from "@/types/index";
import { LIBRARY_AGENTS, CUSTOM_AGENTS } from "./AgentLibraryData";

interface AgentLibraryProps {
  isOpen: boolean;
  onClose: () => void;
  onAddAgent?: (agent: AgentDef) => void;
  currentPipelineType?: string;
  canAddMore?: boolean;
  existingAgentIds?: string[];
}

const ALL_AGENTS = [...LIBRARY_AGENTS, ...CUSTOM_AGENTS];

const CATEGORIES = [
  { id: "all", label: "All Agents" },
  { id: "user_stories", label: "User Stories" },
  { id: "ppt", label: "Presentation" },
  { id: "prototype", label: "Prototype" },
  { id: "validate_pitch", label: "Validate & Pitch" },
  { id: "app_builder", label: "App Builder" },
  { id: "reverse_engineer", label: "Reverse Engineer" },
  { id: "custom", label: "Custom" },
];

export function AgentLibrary({ isOpen, onClose, onAddAgent, currentPipelineType, canAddMore = true, existingAgentIds = [] }: AgentLibraryProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState(currentPipelineType || "all");
  const [addedIds, setAddedIds] = useState<Set<string>>(new Set());

  // Combine existing pipeline agents + newly added ones
  const allExistingIds = new Set([...existingAgentIds, ...Array.from(addedIds)]);

  const filteredAgents = ALL_AGENTS.filter((agent) => {
    const matchesCategory = activeCategory === "all" || agent.pipeline_type === activeCategory;
    const matchesSearch = !searchQuery ||
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase());
    // Hide agents already in the pipeline
    const notAlreadyAdded = !allExistingIds.has(agent.id);
    return matchesCategory && matchesSearch && notAlreadyAdded;
  });

  const handleAdd = (agent: AgentDef) => {
    onAddAgent?.(agent);
    setAddedIds((prev) => new Set(prev).add(`${agent.pipeline_type}-${agent.id}`));
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] flex items-center justify-center p-6"
        >
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/30 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.25 }}
            className="relative w-full max-w-3xl max-h-[85vh] rounded-2xl border border-[#e8e6dc] bg-white shadow-2xl shadow-black/10 overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#e8e6dc]">
              <div>
                <h2 className="text-sm font-semibold text-[#141413]">Agent Library</h2>
                <p className="text-[11px] text-[#87867f] mt-0.5">{filteredAgents.length} agents available • Click + to add to your pipeline</p>
              </div>
              <button onClick={onClose} className="flex items-center justify-center rounded-lg p-2 text-[#87867f] hover:text-[#141413] hover:bg-[#f5f4ed] transition-all">
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Search + Categories */}
            <div className="px-6 py-3 border-b border-[#f0eee6]">
              <div className="flex items-center gap-2 rounded-xl border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 focus-within:border-[#c96442]/40 transition-colors mb-3">
                <Search className="h-3.5 w-3.5 text-[#87867f]" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search agents..."
                  className="flex-1 bg-transparent text-xs text-[#141413] placeholder-[#87867f] focus:outline-none"
                />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {CATEGORIES.map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => setActiveCategory(cat.id)}
                    className={`rounded-full px-2.5 py-1 text-[10px] font-medium transition-all ${
                      activeCategory === cat.id
                        ? "bg-[#c96442] text-white"
                        : "bg-[#f0eee6] text-[#5e5d59] hover:bg-[#e8e6dc] hover:text-[#141413]"
                    }`}
                  >
                    {cat.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Agent Grid */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {filteredAgents.map((agent) => {
                  const agentKey = `${agent.pipeline_type}-${agent.id}`;
                  const isAdded = addedIds.has(agentKey);
                  return (
                  <div
                    key={agentKey}
                    className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-all group ${
                      isAdded ? "border-green-200 bg-green-50" : "border-[#e8e6dc] bg-[#faf9f5] hover:bg-[#f0eee6]"
                    }`}
                  >
                    <span className="text-base flex-shrink-0">{agent.icon}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] font-medium text-[#141413]">{agent.name}</p>
                      <p className="text-[9px] text-[#87867f] truncate">{agent.description}</p>
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <span className="text-[8px] text-[#87867f]">~{agent.estimated_duration}s</span>
                      {onAddAgent && (
                        isAdded ? (
                          <span className="flex items-center justify-center h-6 px-2 rounded-md bg-green-100 text-green-700 text-[9px] font-medium">
                            ✓ Added
                          </span>
                        ) : !canAddMore ? (
                          <span className="flex items-center justify-center h-6 px-2 rounded-md bg-[#f0eee6] text-[#87867f] text-[8px] font-medium">
                            Max reached
                          </span>
                        ) : (
                          <button
                            onClick={() => handleAdd(agent)}
                            className="opacity-0 group-hover:opacity-100 flex items-center justify-center h-6 w-6 rounded-md bg-[#c96442] text-white hover:bg-[#b5573a] transition-all"
                            title="Add to pipeline"
                          >
                            <Plus className="h-3 w-3" />
                          </button>
                        )
                      )}
                    </div>
                  </div>
                  );
                })}
              </div>
              {filteredAgents.length === 0 && (
                <div className="flex items-center justify-center py-12">
                  <p className="text-sm text-[#87867f]">No agents match your search</p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-[#e8e6dc] flex items-center justify-between">
              <p className="text-[10px] text-[#87867f]">Click the + button to add an agent to your pipeline</p>
              <button onClick={onClose} className="rounded-lg bg-[#f0eee6] hover:bg-[#e8e6dc] px-4 py-2 text-xs font-medium text-[#141413] transition-all">
                Done
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
