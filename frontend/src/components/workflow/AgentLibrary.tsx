"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  X,
  Search,
  BookOpen,
  FileText,
  Presentation,
  Layout,
  Plus,
  Sparkles,
  Wrench,
} from "lucide-react";
import type { AgentDef } from "@/types/index";
import { ALL_LIBRARY_AGENTS, PIPELINE_CATEGORIES } from "./AgentLibraryData";

interface AgentLibraryProps {
  isOpen: boolean;
  onClose: () => void;
  onAddAgent?: (agent: AgentDef) => void;
}

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  user_stories: FileText,
  ppt: Presentation,
  prototype: Layout,
  custom: Wrench,
};

const CATEGORY_LABELS: Record<string, string> = {
  user_stories: "User Stories",
  ppt: "Presentation",
  prototype: "Prototype",
  custom: "Custom",
};

export function AgentLibrary({ isOpen, onClose, onAddAgent }: AgentLibraryProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");

  const categories = ["all", "user_stories", "ppt", "prototype", "custom"];

  const filteredAgents = ALL_LIBRARY_AGENTS.filter((agent) => {
    const matchesSearch =
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory =
      selectedCategory === "all" || agent.pipeline_type === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, x: 300 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: 300 }}
        transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
        className="fixed right-0 top-0 bottom-0 w-[380px] z-50 flex flex-col border-l shadow-2xl shadow-black/50"
        style={{ backgroundColor: "var(--theme-bg)", borderColor: "var(--theme-border)" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-grey/10">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/5 border border-white/10">
              <BookOpen className="h-3.5 w-3.5 text-white" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white">Agent Library</h2>
              <p className="text-[10px] text-grey/50">{ALL_LIBRARY_AGENTS.length} agents available</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center rounded-lg p-2 text-grey/50 hover:text-white hover:bg-white/5 transition-all"
            aria-label="Close library"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Search */}
        <div className="px-5 py-3">
          <div className="flex items-center gap-2 rounded-lg border border-grey/15 px-3 py-2" style={{ backgroundColor: "var(--theme-input-bg)" }}>
            <Search className="h-3.5 w-3.5 text-grey/50" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search agents..."
              className="flex-1 bg-transparent text-xs text-white placeholder-grey/40 focus:outline-none"
            />
          </div>
        </div>

        {/* Category tabs */}
        <div className="px-5 pb-3">
          <div className="flex gap-1 rounded-lg bg-white/5 border border-white/10 p-1">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={`flex-1 rounded-md px-2 py-1.5 text-[10px] font-medium transition-all ${
                  selectedCategory === cat
                    ? "bg-white/10 text-white border border-white/10"
                    : "text-grey/60 hover:text-white border border-transparent"
                }`}
              >
                {cat === "all" ? "All" : CATEGORY_LABELS[cat] || cat}
              </button>
            ))}
          </div>
        </div>

        {/* Agent list */}
        <div className="flex-1 overflow-y-auto px-5 pb-4 space-y-2">
          {filteredAgents.map((agent) => {
            const CategoryIcon = CATEGORY_ICONS[agent.pipeline_type] || Sparkles;
            return (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="group rounded-xl border border-grey/10 bg-white/[0.02] p-3 hover:bg-white/[0.04] hover:border-grey/20 transition-all duration-200"
              >
                <div className="flex items-start gap-3">
                  {/* Agent icon */}
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-white/5 border border-white/10 text-sm">
                    {agent.icon}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-white truncate">{agent.name}</span>
                      {agent.has_skill && (
                        <span className="inline-flex items-center rounded-full bg-blue-400/10 px-1.5 py-0.5 text-[8px] font-medium text-blue-400 border border-blue-400/20">
                          Skill
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-grey/60 mt-0.5">{agent.role}</p>
                    <p className="text-[10px] text-grey/40 mt-0.5 line-clamp-1">{agent.description}</p>
                  </div>

                  {/* Category badge + Add button */}
                  <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                    <CategoryIcon className="h-3 w-3 text-grey/40" />
                    {onAddAgent && (
                      <button
                        onClick={() => onAddAgent(agent)}
                        className="opacity-0 group-hover:opacity-100 flex items-center justify-center rounded-md p-1 bg-white/5 border border-white/10 text-grey/60 hover:text-white hover:bg-white/10 transition-all"
                        aria-label={`Add ${agent.name}`}
                      >
                        <Plus className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}

          {filteredAgents.length === 0 && (
            <p className="text-xs text-grey/50 text-center py-8">No agents match your search.</p>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-grey/10 px-5 py-3">
          <p className="text-[10px] text-grey/40 text-center">
            {filteredAgents.length} of {ALL_LIBRARY_AGENTS.length} agents shown
          </p>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
