"use client";

import { motion } from "motion/react";
import {
  Sparkles,
  FileText,
  Layout,
  Presentation,
  GitBranch,
  Workflow,
  ArrowRight,
  Lock,
  Wand2,
} from "lucide-react";
import type { WorkflowType } from "@/types/index";

interface CreationHubProps {
  onSelectFeature: (type: WorkflowType) => void;
}

const FEATURE_CARDS = [
  {
    id: "presentation",
    label: "Craft a stunning presentation",
    description: "Generate an enterprise-grade slide deck with charts, data tables, and compelling visuals — ready to present.",
    icon: Presentation,
    pipelineType: "ppt" as WorkflowType | null,
    enabled: true,
    color: "from-violet-500/15 to-purple-500/15",
    borderColor: "border-violet-500/25",
    iconColor: "text-violet-400",
    badge: null,
  },
  {
    id: "product_requirements",
    label: "Turn an idea into product requirements",
    description: "Shape a fuzzy idea into a PRD with epics, user stories, and Gherkin criteria.",
    icon: FileText,
    pipelineType: "user_stories" as WorkflowType | null,
    enabled: true,
    color: "from-blue-500/15 to-cyan-500/15",
    borderColor: "border-blue-500/25",
    iconColor: "text-blue-400",
    badge: null,
  },
  {
    id: "clickable_prototype",
    label: "Build a clickable prototype",
    description: "Go from stories or sketches to a high-fidelity, navigable prototype in minutes.",
    icon: Layout,
    pipelineType: "prototype" as WorkflowType | null,
    enabled: true,
    color: "from-emerald-500/15 to-green-500/15",
    borderColor: "border-emerald-500/25",
    iconColor: "text-emerald-400",
    badge: null,
  },
  {
    id: "app_builder",
    label: "Build an app from existing material",
    description: "Hand us a deck, a repo, or a brief — we'll deliver a working app, end to end.",
    icon: Workflow,
    pipelineType: "app_builder" as WorkflowType | null,
    enabled: true,
    color: "from-amber-500/15 to-orange-500/15",
    borderColor: "border-amber-500/25",
    iconColor: "text-amber-400",
    badge: null,
  },
  {
    id: "reverse_engineer",
    label: "Reverse-engineer a codebase",
    description: "Map architecture, dependencies, risks, and hidden user journeys from any repo.",
    icon: GitBranch,
    pipelineType: "reverse_engineer" as WorkflowType | null,
    enabled: true,
    color: "from-rose-500/15 to-pink-500/15",
    borderColor: "border-rose-500/25",
    iconColor: "text-rose-400",
    badge: "Featured",
  },
  {
    id: "custom_workflow",
    label: "Design your own workflow",
    description: "Compose specialist agents and skills into a bespoke pipeline for anything else.",
    icon: Wand2,
    pipelineType: "custom" as WorkflowType | null,
    enabled: true,
    color: "from-slate-500/15 to-gray-500/15",
    borderColor: "border-slate-500/25",
    iconColor: "text-slate-400",
    badge: null,
  },
];

/**
 * CreationHub — Full-width home page with 6 feature cards.
 * No sidebar. Enterprise-grade design.
 */
export function CreationHub({ onSelectFeature }: CreationHubProps) {
  return (
    <div className="flex h-full flex-col overflow-y-auto bg-[#f5f4ed]">
      <div className="relative flex-1 flex flex-col items-center justify-center px-4 sm:px-6 md:px-8 py-8 sm:py-12 max-w-6xl mx-auto w-full">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="text-center mb-12"
        >
          <div className="flex items-center justify-center gap-2.5 mb-5">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-[#c96442] to-[#d97757] shadow-md">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <span className="text-[13px] font-semibold text-[#87867f] tracking-wide uppercase">AI Delivery Studio</span>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold text-[#141413] tracking-tight mb-4">
            What would you like to make?
          </h1>
          <p className="text-sm md:text-base text-[#5e5d59] max-w-lg mx-auto leading-relaxed">
            Pick an outcome to begin. We&apos;ll compose the right specialist agents and let you tune them before running.
          </p>
        </motion.div>

        {/* Cards Grid */}
        <div className="w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 max-w-4xl">
          {FEATURE_CARDS.map((card, index) => {
            const Icon = card.icon;
            return (
              <motion.div
                key={card.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.08 + index * 0.06 }}
                whileHover={card.enabled ? { y: -3, scale: 1.01 } : {}}
                whileTap={card.enabled ? { scale: 0.98 } : {}}
                onClick={() => {
                  if (card.enabled && card.pipelineType) {
                    onSelectFeature(card.pipelineType);
                  }
                }}
                role={card.enabled ? "button" : undefined}
                tabIndex={card.enabled ? 0 : -1}
                onKeyDown={(e) => {
                  if (card.enabled && card.pipelineType && (e.key === "Enter" || e.key === " ")) {
                    onSelectFeature(card.pipelineType);
                  }
                }}
                className={`relative flex flex-col rounded-2xl border p-4 sm:p-6 text-left transition-all duration-300 ${
                  card.enabled
                    ? `border-[#e8e6dc] bg-white cursor-pointer hover:shadow-lg hover:shadow-black/5 hover:border-[#c96442]/30`
                    : "border-[#e8e6dc] bg-[#faf9f5] opacity-50 cursor-not-allowed"
                }`}
              >
                {/* Badge */}
                {card.badge && (
                  <div className="absolute top-3 right-3">
                    <span className="text-[9px] font-semibold uppercase tracking-wider bg-[#c96442]/10 text-[#c96442] border border-[#c96442]/20 rounded-full px-2 py-0.5">
                      {card.badge}
                    </span>
                  </div>
                )}

                {/* Disabled lock */}
                {!card.enabled && (
                  <div className="absolute top-3 right-3">
                    <span className="text-[9px] font-medium text-[#87867f] bg-[#f0eee6] border border-[#e8e6dc] rounded-full px-2 py-0.5 flex items-center gap-1">
                      <Lock className="h-2.5 w-2.5" />
                      Coming Soon
                    </span>
                  </div>
                )}

                {/* Icon */}
                <div className={`flex h-10 w-10 items-center justify-center rounded-xl border border-[#e8e6dc] mb-4 ${card.enabled ? "bg-[#faf9f5]" : "bg-[#f0eee6] opacity-40"}`}>
                  <Icon className={`h-5 w-5 ${card.enabled ? card.iconColor : "text-[#87867f]"}`} />
                </div>

                {/* Text */}
                <h3 className={`text-[13px] font-semibold mb-2 leading-snug ${card.enabled ? "text-[#141413]" : "text-[#87867f]"}`}>
                  {card.label}
                </h3>
                <p className={`text-[11px] leading-relaxed flex-1 ${card.enabled ? "text-[#5e5d59]" : "text-[#87867f]"}`}>
                  {card.description}
                </p>

                {/* Arrow indicator for enabled cards */}
                {card.enabled && (
                  <div className="flex items-center gap-1 mt-4 text-[11px] font-medium text-[#c96442]">
                    <ArrowRight className="h-3.5 w-3.5" />
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
