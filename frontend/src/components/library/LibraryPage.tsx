"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Search, Clock } from "lucide-react";
import { LIBRARY_AGENTS, CUSTOM_AGENTS } from "@/components/workflow/AgentLibraryData";
import { AgentCapabilitiesModal } from "@/components/workflow/AgentsPopup";
import type { AgentDef } from "@/types/index";

const ALL_AGENTS_COMBINED = [...LIBRARY_AGENTS, ...CUSTOM_AGENTS];

type CategoryEntry = { id: string; label: string; section?: boolean };

const CATEGORIES: CategoryEntry[] = [
  { id: "all", label: "All" },
  { id: "user_stories", label: "User Stories" },
  { id: "ppt", label: "Presentation" },
  { id: "prototype", label: "Prototype" },
  { id: "app_builder", label: "App Builder" },
  { id: "migration", label: "Migration", section: true },
  { id: "mulesoft_to_springboot", label: "Mulesoft → Spring Boot" },
  { id: "dotnet_to_azure", label: ".NET → Azure" },
  { id: "custom", label: "Custom" },
];

const MIGRATION_TYPES = new Set(["mulesoft_to_springboot", "dotnet_to_azure"]);

const PIPELINE_LABEL: Record<string, string> = {
  user_stories: "User Stories",
  ppt: "Presentation",
  prototype: "Prototype",
  app_builder: "App Builder",
  custom: "Custom",
  mulesoft_to_springboot: "Mulesoft → Spring Boot",
  dotnet_to_azure: ".NET → Azure",
};

const ICON_STYLES = [
  { bg: "#E8EDF5", text: "#1B2A4A" },
  { bg: "#F0EDE8", text: "#5C4A2A" },
  { bg: "#EAF0EA", text: "#2A5C2A" },
  { bg: "#F0E8EE", text: "#5C2A4A" },
  { bg: "#E8EEF0", text: "#2A4A5C" },
  { bg: "#F0EEE8", text: "#5C5A2A" },
];

function getInitials(name: string): string {
  const words = name.replace(/\s+agent$/i, "").split(" ");
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export function LibraryPage() {
  const [activeCategory, setActiveCategory] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<{ agent: AgentDef; index: number } | null>(null);

  const filteredAgents = ALL_AGENTS_COMBINED.filter((agent) => {
    const matchesCategory =
      activeCategory === "all" ||
      (activeCategory === "migration" && MIGRATION_TYPES.has(agent.pipeline_type)) ||
      agent.pipeline_type === activeCategory;
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
              : cat.id === "migration"
              ? ALL_AGENTS_COMBINED.filter((a) => MIGRATION_TYPES.has(a.pipeline_type)).length
              : ALL_AGENTS_COMBINED.filter((a) => a.pipeline_type === cat.id).length;
            const isActive = activeCategory === cat.id;
            const isSubItem = cat.id === "mulesoft_to_springboot" || cat.id === "dotnet_to_azure";
            return (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`flex items-center justify-between w-full px-3 py-2 rounded-lg text-[13px] transition-colors text-left ${
                  isActive
                    ? "bg-gray-100 text-gray-900 font-medium"
                    : cat.section
                    ? "text-gray-700 font-semibold hover:bg-gray-50"
                    : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
                } ${isSubItem ? "pl-6 text-[12px]" : ""}`}
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
            <p className="text-[11px] text-gray-400 mt-0.5">
              {filteredAgents.length} agents available · tap any agent to see its capabilities
            </p>
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
                onClick={() => setSelectedAgent({ agent, index: idx })}
                className="flex flex-col bg-white rounded-xl border border-gray-200 p-4 hover:border-gray-300 hover:shadow-md transition-all cursor-pointer group"
              >
                {/* Icon + name */}
                <div className="flex items-center gap-3 mb-3">
                  <div
                    className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 text-[11px] font-bold group-hover:scale-105 transition-transform"
                    style={{
                      background: ICON_STYLES[idx % ICON_STYLES.length].bg,
                      color: ICON_STYLES[idx % ICON_STYLES.length].text,
                    }}
                  >
                    {getInitials(agent.name)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[12px] font-semibold text-gray-900 leading-tight group-hover:text-[#1B2A4A] transition-colors">
                      {agent.name}
                    </p>
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
                  <span className="flex items-center gap-1 text-[9px] text-gray-400">
                    <Clock className="h-2.5 w-2.5" />
                    ~{agent.estimated_duration}s
                  </span>
                  <span className="text-[9px] text-gray-400 group-hover:text-[#1B2A4A] transition-colors font-medium">
                    Tap to explore →
                  </span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>

      {/* Capabilities modal */}
      <AnimatePresence>
        {selectedAgent && (
          <AgentCapabilitiesModal
            agent={selectedAgent.agent}
            agentIndex={selectedAgent.index}
            onClose={() => setSelectedAgent(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
