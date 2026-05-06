"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { FileText, Presentation, Layout, Zap, Search, Layers } from "lucide-react";
import { LIBRARY_AGENTS, CUSTOM_AGENTS } from "@/components/workflow/AgentLibraryData";

const ALL_AGENTS_COMBINED = [...LIBRARY_AGENTS, ...CUSTOM_AGENTS];

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

export function LibraryPage() {
  const [activeCategory, setActiveCategory] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredAgents = ALL_AGENTS_COMBINED.filter((agent) => {
    const matchesCategory = activeCategory === "all" || agent.pipeline_type === activeCategory;
    const matchesSearch = !searchQuery || agent.name.toLowerCase().includes(searchQuery.toLowerCase()) || agent.description.toLowerCase().includes(searchQuery.toLowerCase()) || agent.role.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  }).sort((a, b) => a.pipeline_type.localeCompare(b.pipeline_type) || a.order - b.order);

  const getCategoryColor = (type: string) => {
    switch (type) {
      case "user_stories": return "text-blue-600 bg-blue-50 border-blue-200";
      case "ppt": return "text-amber-600 bg-amber-50 border-amber-200";
      case "prototype": return "text-emerald-600 bg-emerald-50 border-emerald-200";
      case "validate_pitch": return "text-violet-600 bg-violet-50 border-violet-200";
      case "app_builder": return "text-orange-600 bg-orange-50 border-orange-200";
      case "reverse_engineer": return "text-rose-600 bg-rose-50 border-rose-200";
      case "custom": return "text-purple-600 bg-purple-50 border-purple-200";
      default: return "text-[#5e5d59] bg-[#f0eee6] border-[#e8e6dc]";
    }
  };

  return (
    <div className="flex flex-col sm:flex-row h-full bg-[#f5f4ed]">
      {/* Left Sidebar — hidden on mobile, shown as horizontal scroll */}
      <div className="w-full sm:w-[200px] lg:w-[220px] flex-shrink-0 border-b sm:border-b-0 sm:border-r border-[#e8e6dc] flex sm:flex-col py-3 sm:py-5 px-3 sm:px-4 bg-white overflow-x-auto sm:overflow-x-visible">
        <h2 className="text-xs font-semibold text-[#87867f] uppercase tracking-wider mb-2 sm:mb-4 px-2 hidden sm:block">Categories</h2>
        <div className="flex sm:flex-col gap-1 sm:space-y-1 min-w-max sm:min-w-0">
          {CATEGORIES.map((cat) => {
            const Icon = cat.icon;
            const isActive = activeCategory === cat.id;
            const count = cat.id === "all" ? ALL_AGENTS_COMBINED.length : ALL_AGENTS_COMBINED.filter((a) => a.pipeline_type === cat.id).length;
            return (
              <button key={cat.id} onClick={() => setActiveCategory(cat.id)}
                className={`w-full flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-[12px] font-medium transition-all ${isActive ? "bg-[#f5f4ed] text-[#141413] border border-[#e8e6dc]" : "text-[#5e5d59] hover:text-[#141413] hover:bg-[#faf9f5] border border-transparent"}`}>
                <Icon className="h-4 w-4" />
                <span className="flex-1 text-left">{cat.label}</span>
                <span className="text-[10px] text-[#87867f] bg-[#f0eee6] rounded-full px-1.5 py-0.5">{count}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Right Content */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="px-6 py-4 border-b border-[#e8e6dc] bg-white">
          <div className="flex items-center gap-2 rounded-xl border border-[#e8e6dc] bg-[#faf9f5] px-4 py-2.5 focus-within:border-[#c96442]/40 transition-colors max-w-md">
            <Search className="h-4 w-4 text-[#87867f]" />
            <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Search agents by name, role, or description..."
              className="flex-1 bg-transparent text-sm text-[#141413] placeholder-[#87867f] focus:outline-none" />
          </div>
          <p className="text-[11px] text-[#87867f] mt-2">{filteredAgents.length} agents available</p>
        </div>

        <div className="flex-1 overflow-y-auto px-3 sm:px-6 py-4 sm:py-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2 sm:gap-3">
            {filteredAgents.map((agent, idx) => (
              <motion.div key={`${agent.pipeline_type}-${agent.id}`} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(idx * 0.02, 0.5) }}
                className="flex flex-col rounded-xl border border-[#e8e6dc] bg-white hover:shadow-md hover:border-[#c96442]/20 p-4 transition-all">
                <div className="flex items-start gap-3 mb-3">
                  <span className="text-lg">{agent.icon}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-[12px] font-semibold text-[#141413]">{agent.name}</p>
                    <p className="text-[10px] text-[#87867f] mt-0.5">{agent.role}</p>
                  </div>
                </div>
                <p className="text-[10px] text-[#5e5d59] leading-relaxed flex-1 mb-3">{agent.description}</p>
                <div className="flex items-center justify-between">
                  <span className={`text-[9px] font-medium rounded-full px-2 py-0.5 border ${getCategoryColor(agent.pipeline_type)}`}>
                    {agent.pipeline_type === "user_stories" ? "Stories" : agent.pipeline_type === "ppt" ? "PPT" : agent.pipeline_type === "prototype" ? "Prototype" : agent.pipeline_type === "validate_pitch" ? "Pitch" : agent.pipeline_type === "app_builder" ? "App" : agent.pipeline_type === "reverse_engineer" ? "Reverse" : "Custom"}
                  </span>
                  <span className="text-[9px] text-[#87867f] flex items-center gap-0.5"><Zap className="h-2.5 w-2.5" />~{agent.estimated_duration}s</span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
