"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, Search, Plus, Zap, CheckCircle2 } from "lucide-react";
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
  { id: "app_builder", label: "App Builder" },
  { id: "reverse_engineer", label: "Reverse Engineer" },
  { id: "custom", label: "Custom" },
];

export function AgentLibrary({ isOpen, onClose, onAddAgent, currentPipelineType, canAddMore = true, existingAgentIds = [] }: AgentLibraryProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState(currentPipelineType || "all");
  const [addedIds, setAddedIds] = useState<Set<string>>(new Set());

  const allExistingIds = new Set([...existingAgentIds, ...Array.from(addedIds)]);

  const HIDDEN_FROM_CUSTOM = new Set([
    "ppt-assembler", "backlog-compiler", "prototype-finalizer", "app-assembler", "documentation-generator",
    "ppt-content-strategist", "domain-analyst", "requirements-analyst", "material-analyzer", "repo-scanner",
  ]);

  const filteredAgents = ALL_AGENTS.filter((agent) => {
    const matchesCategory = activeCategory === "all" || agent.pipeline_type === activeCategory;
    const matchesSearch =
      !searchQuery ||
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase());
    const notAlreadyAdded = !allExistingIds.has(agent.id);
    const notHidden = currentPipelineType !== "custom" || !HIDDEN_FROM_CUSTOM.has(agent.id);
    return matchesCategory && matchesSearch && notAlreadyAdded && notHidden;
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
            className="relative w-full max-w-3xl max-h-[85vh] rounded-xl border border-gray-200 bg-white shadow-2xl shadow-black/10 overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Agent Library</h2>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  {filteredAgents.length} agents available · Click + to add to your pipeline
                </p>
              </div>
              <button
                onClick={onClose}
                className="flex items-center justify-center rounded-lg p-2 text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-all"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Search + Categories */}
            <div className="px-6 py-3 border-b border-gray-100">
              <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 focus-within:border-blue-400 focus-within:ring-1 focus-within:ring-blue-400 transition-all mb-3">
                <Search className="h-3.5 w-3.5 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search agents..."
                  className="flex-1 bg-transparent text-xs text-gray-900 placeholder-gray-400 focus:outline-none"
                />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {CATEGORIES.map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => setActiveCategory(cat.id)}
                    className={`rounded-full px-2.5 py-1 text-[10px] font-medium transition-all ${
                      activeCategory === cat.id
                        ? "bg-blue-600 text-white"
                        : "bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-900"
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
                      className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-all group ${
                        isAdded
                          ? "border-emerald-200 bg-emerald-50"
                          : "border-gray-200 bg-gray-50 hover:bg-gray-100"
                      }`}
                    >
                      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gray-200 flex-shrink-0">
                        <Zap className="h-3.5 w-3.5 text-gray-500" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] font-medium text-gray-900">{agent.name}</p>
                        <p className="text-[9px] text-gray-500 truncate">{agent.description}</p>
                      </div>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <span className="text-[8px] text-gray-400">~{agent.estimated_duration}s</span>
                        {onAddAgent && (
                          isAdded ? (
                            <span className="flex items-center gap-1 h-6 px-2 rounded-md bg-emerald-100 text-emerald-700 text-[9px] font-medium">
                              <CheckCircle2 className="h-3 w-3" /> Added
                            </span>
                          ) : !canAddMore ? (
                            <span className="flex items-center justify-center h-6 px-2 rounded-md bg-gray-100 text-gray-400 text-[8px] font-medium">
                              Max reached
                            </span>
                          ) : (
                            <button
                              onClick={() => handleAdd(agent)}
                              className="opacity-0 group-hover:opacity-100 flex items-center justify-center h-6 w-6 rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-all"
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
                  <p className="text-sm text-gray-400">No agents match your search</p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-gray-200 flex items-center justify-between">
              <p className="text-[10px] text-gray-400">Click the + button to add an agent to your pipeline</p>
              <button
                onClick={onClose}
                className="rounded-lg bg-gray-100 hover:bg-gray-200 px-4 py-2 text-xs font-medium text-gray-700 transition-all"
              >
                Done
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
