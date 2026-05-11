"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { X, Search } from "lucide-react";
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
  { id: "all", label: "All" },
  { id: "user_stories", label: "User Stories" },
  { id: "ppt", label: "Presentation" },
  { id: "prototype", label: "Prototype" },
  { id: "app_builder", label: "App Builder" },
  { id: "custom", label: "Custom" },
];

const HIDDEN_FROM_CUSTOM = new Set([
  "ppt-assembler", "backlog-compiler", "prototype-finalizer", "app-assembler",
  "ppt-content-strategist", "domain-analyst", "requirements-analyst", "material-analyzer",
]);

// Monochrome icon — no colors, just gray
function getInitials(name: string): string {
  const words = name.replace(/\s+agent$/i, "").split(" ");
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export function AgentLibrary({
  isOpen, onClose, onAddAgent, currentPipelineType, canAddMore = true, existingAgentIds = [],
}: AgentLibraryProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState(currentPipelineType || "all");

  // Use only existingAgentIds from parent — no local tracking
  // This ensures removed agents reappear in the library
  const filteredAgents = ALL_AGENTS.filter((agent) => {
    const matchesCategory = activeCategory === "all" || agent.pipeline_type === activeCategory;
    const matchesSearch =
      !searchQuery ||
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase());
    const notAlreadyAdded = !existingAgentIds.includes(agent.id);
    const notHidden = currentPipelineType !== "custom" || !HIDDEN_FROM_CUSTOM.has(agent.id);
    return matchesCategory && matchesSearch && notAlreadyAdded && notHidden;
  });

  const categoryCounts: Record<string, number> = { all: 0 };
  ALL_AGENTS.forEach((a) => {
    if (!existingAgentIds.includes(a.id)) {
      categoryCounts.all = (categoryCounts.all || 0) + 1;
      categoryCounts[a.pipeline_type] = (categoryCounts[a.pipeline_type] || 0) + 1;
    }
  });

  const handleAdd = (agent: AgentDef) => {
    if (!canAddMore) return;
    onAddAgent?.(agent);
    onClose(); // Close library so user sees the agent added to the flow
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[70] flex items-center justify-center p-6"
        >
          {/* Backdrop */}
          <motion.div
            className="absolute inset-0 bg-black/40 backdrop-blur-[2px]"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 12 }}
            transition={{ duration: 0.18 }}
            className="relative w-full max-w-[820px] rounded-2xl shadow-2xl overflow-hidden flex"
            style={{ height: "640px", background: "#f5f5f0" }}          >
            {/* Left sidebar — categories */}
            <div className="w-[180px] flex-shrink-0 border-r border-gray-100 flex flex-col bg-white">
              <div className="px-5 pt-6 pb-4 border-b border-gray-100">
                <h2 className="text-[16px] font-bold text-gray-900">Add agent</h2>
              </div>
              <nav className="flex-1 overflow-y-auto py-2">
                {CATEGORIES.map((cat) => {
                  const count = categoryCounts[cat.id] || 0;
                  const isActive = activeCategory === cat.id;
                  return (
                    <button
                      key={cat.id}
                      onClick={() => setActiveCategory(cat.id)}
                      className={`w-full flex items-center justify-between px-5 py-2 text-[13px] transition-colors text-left ${
                        isActive
                          ? "bg-gray-100 text-gray-900 font-medium"
                          : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
                      }`}
                    >
                      <span>{cat.label}</span>
                    </button>
                  );
                })}
              </nav>
            </div>

            {/* Right content */}
            <div className="flex-1 flex flex-col min-w-0">
              {/* Header */}
              <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-gray-100 flex-shrink-0 bg-white">
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search agents..."
                    className="w-full pl-9 pr-4 py-2 text-[12px] bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 transition-colors placeholder-gray-400"
                  />
                </div>
                <button
                  onClick={onClose}
                  className="h-8 w-8 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-all ml-4"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* Agent grid */}
              <div className="flex-1 overflow-y-auto p-4" style={{ background: "#f5f5f0" }}>
                {filteredAgents.length === 0 ? (
                  <div className="flex items-center justify-center h-full">
                    <p className="text-[13px] text-gray-400">No agents found</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    {filteredAgents.map((agent, idx) => {
                      const initials = getInitials(agent.name);
                      const categoryLabel = CATEGORIES.find(c => c.id === agent.pipeline_type)?.label?.toUpperCase() || agent.pipeline_type.toUpperCase();

                      return (
                        <motion.button
                          key={`${agent.pipeline_type}-${agent.id}`}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: idx * 0.02 }}
                          onClick={() => handleAdd(agent)}
                          disabled={!canAddMore}
                          className={`flex items-start gap-3 rounded-xl border px-4 py-3.5 text-left transition-all group ${
                            canAddMore
                              ? "border-gray-200 bg-gray-50 hover:bg-white hover:border-gray-300 hover:shadow-sm cursor-pointer"
                              : "border-gray-100 bg-gray-50 opacity-50 cursor-not-allowed"
                          }`}
                        >
                          {/* Icon */}
                          <div className="w-9 h-9 rounded-lg bg-gray-100 border border-gray-200 flex items-center justify-center flex-shrink-0 text-[11px] font-bold text-gray-500">
                            {getInitials(agent.name)}
                          </div>

                          {/* Info */}
                          <div className="flex-1 min-w-0">
                            <p className="text-[13px] font-semibold text-gray-900 leading-tight">
                              {agent.name}
                            </p>
                            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mt-0.5 mb-1.5">
                              {categoryLabel}
                            </p>
                            <p className="text-[11px] text-gray-500 leading-relaxed line-clamp-2">
                              {agent.description}
                            </p>
                          </div>
                        </motion.button>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
