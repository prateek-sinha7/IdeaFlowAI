"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { FileText, Presentation, Layout, Zap, Search, Layers } from "lucide-react";
import { LIBRARY_AGENTS } from "@/components/workflow/AgentLibraryData";
import type { AgentDef } from "@/types/index";

const CATEGORIES = [
  { id: "all", label: "All Agents", icon: Layers },
  { id: "user_stories", label: "User Stories", icon: FileText },
  { id: "ppt", label: "Presentation", icon: Presentation },
  { id: "prototype", label: "Prototype", icon: Layout },
  { id: "validate_pitch", label: "Validate & Pitch", icon: FileText },
  { id: "app_builder", label: "App Builder", icon: Layout },
  { id: "reverse_engineer", label: "Reverse Engineer", icon: FileText },
  { id: "custom", label: "Custom", icon: Layers },
];

/**
 * Library Page — shows all available agents organized by category.
 * Left sidebar: category filter. Right: agent grid.
 */
export function LibraryPage() {
  const [activeCategory, setActiveCategory] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredAgents = LIBRARY_AGENTS.filter((agent) => {
    const matchesCategory = activeCategory === "all" || agent.pipeline_type === activeCategory;
    const matchesSearch = !searchQuery ||
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  }).sort((a, b) => a.pipeline_type.localeCompare(b.pipeline_type) || a.order - b.order);

  const getCategoryColor = (type: string) => {
    switch (type) {
      case "user_stories": return "text-blue-400 bg-blue-500/10 border-blue-500/20";
      case "ppt": return "text-amber-400 bg-amber-500/10 border-amber-500/20";
      case "prototype": return "text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
      case "validate_pitch": return "text-violet-400 bg-violet-500/10 border-violet-500/20";
      case "app_builder": return "text-orange-400 bg-orange-500/10 border-orange-500/20";
      case "reverse_engineer": return "text-rose-400 bg-rose-500/10 border-rose-500/20";
      case "custom": return "text-purple-400 bg-purple-500/10 border-purple-500/20";
      default: return "text-white/50 bg-white/5 border-white/10";
    }
  };

  return (
    <div className="flex h-full" style={{ backgroundColor: "var(--theme-bg)" }}>
      {/* Left Sidebar — Categories */}
      <div className="w-[220px] flex-shrink-0 border-r border-white/8 flex flex-col py-5 px-4">
        <h2 className="text-xs font-semibold text-white/70 uppercase tracking-wider mb-4 px-2">Categories</h2>
        <div className="space-y-1">
          {CATEGORIES.map((cat) => {
            const Icon = cat.icon;
            const isActive = activeCategory === cat.id;
            const count = cat.id === "all"
              ? LIBRARY_AGENTS.length
              : LIBRARY_AGENTS.filter((a) => a.pipeline_type === cat.id).length;

            return (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-[12px] font-medium transition-all ${
                  isActive
                    ? "bg-white/10 text-white border border-white/10"
                    : "text-white/50 hover:text-white hover:bg-white/5 border border-transparent"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span className="flex-1 text-left">{cat.label}</span>
                <span className="text-[10px] text-white/30 bg-white/5 rounded-full px-1.5 py-0.5">{count}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Right Content — Agent Grid */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Search bar */}
        <div className="px-6 py-4 border-b border-white/8">
          <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-2.5 focus-within:border-white/20 transition-colors max-w-md">
            <Search className="h-4 w-4 text-white/30" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search agents by name, role, or description..."
              className="flex-1 bg-transparent text-sm text-white placeholder-white/30 focus:outline-none"
            />
          </div>
          <p className="text-[11px] text-white/30 mt-2">{filteredAgents.length} agents available</p>
        </div>

        {/* Agent Grid */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {filteredAgents.map((agent, idx) => (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.02 }}
                className="flex flex-col rounded-xl border border-white/8 bg-white/[0.02] hover:bg-white/[0.04] hover:border-white/15 p-4 transition-all"
              >
                <div className="flex items-start gap-3 mb-3">
                  <span className="text-lg">{agent.icon}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-[12px] font-semibold text-white/90">{agent.name}</p>
                    <p className="text-[10px] text-white/40 mt-0.5">{agent.role}</p>
                  </div>
                </div>
                <p className="text-[10px] text-white/40 leading-relaxed flex-1 mb-3">{agent.description}</p>
                <div className="flex items-center justify-between">
                  <span className={`text-[9px] font-medium rounded-full px-2 py-0.5 border ${getCategoryColor(agent.pipeline_type)}`}>
                    {agent.pipeline_type === "user_stories" ? "Stories" : agent.pipeline_type === "ppt" ? "PPT" : "Prototype"}
                  </span>
                  <span className="text-[9px] text-white/25 flex items-center gap-0.5">
                    <Zap className="h-2.5 w-2.5" />
                    ~{agent.estimated_duration}s
                  </span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
