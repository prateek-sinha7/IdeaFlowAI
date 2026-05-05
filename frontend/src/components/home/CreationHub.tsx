"use client";

import { useState } from "react";
import { motion } from "motion/react";
import {
  FileText,
  Presentation,
  Layout,
  Zap,
  Sparkles,
} from "lucide-react";
import type { WorkflowType } from "@/types/index";

interface CreationHubProps {
  onSelectFeature: (type: WorkflowType) => void;
}

const WORKFLOW_CARDS = [
  {
    id: "user_stories" as WorkflowType,
    label: "User Stories",
    tagline: "From idea to sprint-ready backlog",
    description:
      "Turn a rough concept into a complete product backlog — personas, epics, prioritized stories with acceptance criteria, and story points. Ready for your next sprint planning.",
    icon: FileText,
    color: "from-blue-500/20 to-cyan-500/20",
    hoverColor: "hover:from-blue-500/30 hover:to-cyan-500/30",
    borderColor: "border-blue-500/30",
    textColor: "text-blue-400",
    accentBg: "bg-blue-500/10",
    agents: 12,
    estimatedTime: "~60s",
  },
  {
    id: "ppt" as WorkflowType,
    label: "Presentation",
    tagline: "Pitch-perfect decks in seconds",
    description:
      "Craft a compelling narrative with structured slides, data visualizations, speaker notes, and a polished visual flow — whether you're pitching investors or aligning your team.",
    icon: Presentation,
    color: "from-amber-500/20 to-orange-500/20",
    hoverColor: "hover:from-amber-500/30 hover:to-orange-500/30",
    borderColor: "border-amber-500/30",
    textColor: "text-amber-400",
    accentBg: "bg-amber-500/10",
    agents: 10,
    estimatedTime: "~45s",
  },
  {
    id: "prototype" as WorkflowType,
    label: "Prototype",
    tagline: "See your product before you build it",
    description:
      "Generate a clickable UI prototype with page layouts, navigation flows, component hierarchy, and interactive states — so you can validate ideas before writing a single line of code.",
    icon: Layout,
    color: "from-emerald-500/20 to-green-500/20",
    hoverColor: "hover:from-emerald-500/30 hover:to-green-500/30",
    borderColor: "border-emerald-500/30",
    textColor: "text-emerald-400",
    accentBg: "bg-emerald-500/10",
    agents: 12,
    estimatedTime: "~60s",
  },
];

/**
 * CreationHub — Step 1 of the workflow.
 * Shows only the feature cards.
 * Clicking a card navigates to Step 2 (WorkflowView build step).
 */
export function CreationHub({ onSelectFeature }: CreationHubProps) {
  return (
    <div className="flex h-full flex-col overflow-y-auto" style={{ backgroundColor: "var(--theme-bg)" }}>
      {/* Ambient background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div
          className="absolute top-1/4 left-1/3 w-[500px] h-[500px] rounded-full opacity-[0.04]"
          style={{ background: "radial-gradient(circle, #3b82f6, transparent 70%)", filter: "blur(80px)" }}
        />
        <div
          className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] rounded-full opacity-[0.03]"
          style={{ background: "radial-gradient(circle, #8b5cf6, transparent 70%)", filter: "blur(70px)" }}
        />
      </div>

      <div className="relative flex-1 flex flex-col items-center px-6 py-10 max-w-5xl mx-auto w-full">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-10"
        >
          <div className="flex items-center justify-center gap-2 mb-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/5 border border-white/10">
              <Sparkles className="h-5 w-5 text-white/80" />
            </div>
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight mb-3">
            What would you like to create?
          </h1>
          <p className="text-sm text-grey/60 max-w-md mx-auto leading-relaxed">
            Select a workflow to get started. Our AI agents will guide you through the rest.
          </p>
        </motion.div>

        {/* Workflow Cards — the only interactive element on this page */}
        <div className="w-full grid grid-cols-1 md:grid-cols-3 gap-4 mb-10">
          {WORKFLOW_CARDS.map((card, index) => {
            const Icon = card.icon;
            return (
              <motion.div
                key={card.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.1 + index * 0.08 }}
                whileHover={{ y: -4, scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => onSelectFeature(card.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelectFeature(card.id); }}
                className={`relative flex flex-col rounded-2xl border ${card.borderColor} p-6 text-left transition-all duration-300 cursor-pointer bg-gradient-to-br ${card.color} hover:shadow-lg hover:shadow-black/20`}
              >
                {/* Icon + metadata */}
                <div className="flex items-start justify-between mb-4">
                  <div className={`flex h-12 w-12 items-center justify-center rounded-xl ${card.accentBg} border border-white/10`}>
                    <Icon className={`h-6 w-6 ${card.textColor}`} />
                  </div>
                  <div className="flex items-center gap-1 text-[10px] text-grey/50 bg-black/20 rounded-full px-2 py-1">
                    <Zap className="h-2.5 w-2.5" />
                    {card.agents} agents • {card.estimatedTime}
                  </div>
                </div>

                {/* Text */}
                <h3 className="text-base font-semibold text-white mb-1">{card.label}</h3>
                <p className={`text-xs ${card.textColor} font-medium mb-2`}>{card.tagline}</p>
                <p className="text-[11px] text-grey/55 leading-relaxed">{card.description}</p>
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

