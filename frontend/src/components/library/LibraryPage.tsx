"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { Search, Clock } from "lucide-react";
import { LIBRARY_AGENTS, CUSTOM_AGENTS } from "@/components/workflow/AgentLibraryData";

const ALL_AGENTS_COMBINED = [...LIBRARY_AGENTS, ...CUSTOM_AGENTS];

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "user_stories", label: "User Stories" },
  { id: "ppt", label: "Presentation" },
  { id: "prototype", label: "Prototype" },
  { id: "app_builder", label: "App Builder" },
  { id: "custom", label: "Custom" },
];

const PIPELINE_LABEL: Record<string, string> = {
  user_stories: "User Stories",
  ppt: "Presentation",
  prototype: "Prototype",
  app_builder: "App Builder",
  custom: "Custom",
};

function getInitials(name: string): string {
  const words = name.replace(/\s+agent$/i, "").split(" ");
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export function LibraryPage() {
  const [activeCategory, setActiveCategory] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  const filteredAgents = ALL_AGENTS_COMBINED.filter((agent) => {
    const matchesCategory = activeCategory === "all" || agent.pipeline_type === activeCategory;
    const matchesSearch =
      !searchQuery ||
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.role.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCategory && matchesSearch;
  }).sort((a, b) => a.pipeline_type.localeCompare(b.pipeline_type) || a.order - b.order);

  return (
    <div className="flex h-full" style={{ background: "#f5f5f0" }}>
      {/* Left Sidebar */}
      <div className="w-[200px] flex-shrink-0 bg-white border-r border-gray-200 flex flex-col py-5">
        <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-[0.15em] px-5 mb-3">
          Categories
        </p>
        <nav className="flex flex-col gap-0.5 px-3">
          {CATEGORIES.map((cat) => {
            const count = cat.id === "all"
              ? ALL_AGENTS_COMBINED.length
              : ALL_AGENTS_COMBINED.filter((a) => a.pipeline_type === cat.id).length;
            const isActive = activeCategory === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`flex items-center justify-between w-full px-3 py-2 rounded-lg text-[13px] transition-colors text-left ${
                  isActive
                    ? "bg-gray-100 text-gray-900 font-medium"
                    : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
                }`}
              >
                <span>{cat.label}</span>
                <span className={`text-[11px] font-medium ${isActive ? "text-gray-600" : "text-gray-400"}`}>
                  {count}
                </span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar */}
        <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200 flex-shrink-0">
          <div>
            <h1 className="text-[15px] font-semibold text-gray-900">Agent Library</h1>
            <p className="text-[11px] text-gray-400 mt-0.5">{filteredAgents.length} agents available</p>
          </div>
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search agents..."
              className="w-full pl-9 pr-4 py-2 text-[12px] bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:border-gray-400 transition-colors placeholder-gray-400"
            />
          </div>
        </div>

        {/* Agent grid */}
        <div className="flex-1 overflow-y-auto p-5">
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {filteredAgents.map((agent, idx) => (
              <motion.div
                key={`${agent.pipeline_type}-${agent.id}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: Math.min(idx * 0.015, 0.4) }}
                className="flex flex-col bg-white rounded-xl border border-gray-200 p-4 hover:border-gray-300 hover:shadow-sm transition-all cursor-default"
              >
                {/* Icon + name */}
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-9 h-9 rounded-lg bg-gray-100 border border-gray-200 flex items-center justify-center flex-shrink-0">
                    <span className="text-[11px] font-bold text-gray-500 select-none">
                      {getInitials(agent.name)}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[12px] font-semibold text-gray-900 leading-tight">{agent.name}</p>
                    <p className="text-[10px] text-gray-400 mt-0.5 uppercase tracking-wide font-medium">
                      {PIPELINE_LABEL[agent.pipeline_type] ?? agent.pipeline_type}
                    </p>
                  </div>
                </div>

                {/* Role */}
                <p className="text-[10px] font-semibold text-gray-500 mb-1.5">{agent.role}</p>

                {/* Description */}
                <p className="text-[11px] text-gray-500 leading-relaxed flex-1 mb-3 line-clamp-3">
                  {agent.description}
                </p>

                {/* Footer */}
                <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                  <span className="text-[9px] font-semibold text-gray-400 uppercase tracking-wide">
                    {PIPELINE_LABEL[agent.pipeline_type] ?? agent.pipeline_type}
                  </span>
                  <span className="flex items-center gap-1 text-[9px] text-gray-400">
                    <Clock className="h-2.5 w-2.5" />
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
