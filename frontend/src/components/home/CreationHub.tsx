"use client";

import { motion } from "motion/react";
import { ArrowRight } from "lucide-react";
import type { WorkflowType } from "@/types/index";

interface CreationHubProps {
  onSelectFeature: (type: WorkflowType) => void;
}

const WORKFLOWS = [
  {
    id: "user_stories",
    type: "user_stories" as WorkflowType,
    label: "Turn an idea into product requirements",
    description: "Shape a fuzzy idea into a PRD with epics, user stories, and Gherkin acceptance criteria.",
    badge: null,
  },
  {
    id: "ppt",
    type: "ppt" as WorkflowType,
    label: "Craft a presentation",
    description: "Generate an enterprise-grade slide deck with charts, data tables, and compelling visuals.",
    badge: null,
  },
  {
    id: "prototype",
    type: "prototype" as WorkflowType,
    label: "Build a clickable prototype",
    description: "Go from stories or sketches to a high-fidelity, navigable prototype in minutes.",
    badge: null,
  },
  {
    id: "app_builder",
    type: "app_builder" as WorkflowType,
    label: "Build an app from existing material",
    description: "Hand us a deck, a repo, or a brief — we'll deliver a working app, end to end.",
    badge: null,
  },
  {
    id: "custom",
    type: "custom" as WorkflowType,
    label: "Design your own workflow",
    description: "Compose specialist agents and skills into a bespoke pipeline for anything else.",
    badge: null,
  },
];

export function CreationHub({ onSelectFeature }: CreationHubProps) {
  return (
    <div
      className="flex h-full flex-col overflow-y-auto"
      style={{ background: "#f5f5f0" }}
    >
      <div className="flex-1 flex flex-col items-center px-6 py-12 max-w-2xl mx-auto w-full">

        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="text-center mb-12 w-full"
        >
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-[0.18em] mb-5">
            IdeaFlow AI
          </p>
          <h1 className="text-[38px] sm:text-[44px] font-bold text-gray-900 leading-tight tracking-tight mb-4">
            What would you like to make?
          </h1>
          <p className="text-[14px] text-gray-500 leading-relaxed max-w-md mx-auto">
            Pick an outcome to begin. We'll compose the right specialist agents and let you tune them before running.
          </p>
        </motion.div>

        {/* Workflow list */}
        <div className="w-full divide-y divide-gray-200/70">
          {WORKFLOWS.map((workflow, idx) => (
            <motion.button
              key={workflow.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 + idx * 0.06 }}
              onClick={() => onSelectFeature(workflow.type)}
              className="group w-full flex items-start justify-between gap-4 py-5 text-left hover:bg-white/60 transition-colors rounded-lg px-3 -mx-3"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-[15px] font-semibold text-gray-900 italic leading-snug group-hover:text-[#1B2A4A] transition-colors">
                    {workflow.label}
                  </h2>
                  {workflow.badge && (
                    <span className="text-[9px] font-semibold text-[#1B2A4A] border border-[#1B2A4A]/30 px-1.5 py-0.5 rounded uppercase tracking-wide">
                      {workflow.badge}
                    </span>
                  )}
                </div>
                <p className="text-[12px] text-gray-500 leading-relaxed">
                  {workflow.description}
                </p>
              </div>
              <div className="flex-shrink-0 mt-1">
                <ArrowRight className="h-4 w-4 text-gray-300 group-hover:text-gray-600 group-hover:translate-x-0.5 transition-all" />
              </div>
            </motion.button>
          ))}
        </div>

      </div>
    </div>
  );
}
