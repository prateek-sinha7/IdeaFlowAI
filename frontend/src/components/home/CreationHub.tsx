"use client";

import { motion } from "motion/react";
import {
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
    label: "Craft a Presentation",
    description: "Generate an enterprise-grade slide deck with charts, data tables, and compelling visuals — ready to present.",
    icon: Presentation,
    pipelineType: "ppt" as WorkflowType | null,
    enabled: true,
    badge: null,
  },
  {
    id: "product_requirements",
    label: "Product Requirements",
    description: "Shape a fuzzy idea into a PRD with epics, user stories, and Gherkin acceptance criteria.",
    icon: FileText,
    pipelineType: "user_stories" as WorkflowType | null,
    enabled: true,
    badge: null,
  },
  {
    id: "clickable_prototype",
    label: "Clickable Prototype",
    description: "Go from stories or sketches to a high-fidelity, navigable prototype in minutes.",
    icon: Layout,
    pipelineType: "prototype" as WorkflowType | null,
    enabled: true,
    badge: null,
  },
  {
    id: "app_builder",
    label: "Build an App",
    description: "Hand us a deck, a repo, or a brief — we'll deliver a working app, end to end.",
    icon: Workflow,
    pipelineType: "app_builder" as WorkflowType | null,
    enabled: true,
    badge: null,
  },
  {
    id: "reverse_engineer",
    label: "Reverse-Engineer a Codebase",
    description: "Map architecture, dependencies, risks, and hidden user journeys from any repo.",
    icon: GitBranch,
    pipelineType: "reverse_engineer" as WorkflowType | null,
    enabled: true,
    badge: "Featured",
  },
  {
    id: "custom_workflow",
    label: "Custom Workflow",
    description: "Compose specialist agents and skills into a bespoke pipeline for anything else.",
    icon: Wand2,
    pipelineType: "custom" as WorkflowType | null,
    enabled: true,
    badge: null,
  },
];

export function CreationHub({ onSelectFeature }: CreationHubProps) {
  return (
    <div className="flex h-full flex-col overflow-y-auto bg-gray-50">
      <div className="relative flex-1 flex flex-col items-center justify-center px-4 sm:px-6 md:px-8 py-8 sm:py-12 max-w-6xl mx-auto w-full">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="text-center mb-10"
        >
          <h1 className="text-2xl font-semibold text-gray-900 tracking-tight mb-2">
            What would you like to build?
          </h1>
          <p className="text-sm text-gray-500">
            Choose a workflow to get started with AI-powered delivery
          </p>
        </motion.div>

        {/* Cards Grid */}
        <div className="w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 max-w-4xl">
          {FEATURE_CARDS.map((card, index) => {
            const Icon = card.icon;
            return (
              <motion.div
                key={card.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35, delay: 0.06 + index * 0.05 }}
                whileHover={card.enabled ? { y: -2 } : {}}
                whileTap={card.enabled ? { scale: 0.99 } : {}}
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
                className={`relative flex flex-col rounded-lg border bg-white p-5 text-left transition-all duration-200 shadow-sm ${
                  card.enabled
                    ? "border-gray-200 cursor-pointer hover:border-blue-300 hover:shadow-md"
                    : "border-gray-200 opacity-50 cursor-not-allowed"
                }`}
              >
                {/* Badge */}
                {card.badge && (
                  <div className="absolute top-3 right-3">
                    <span className="text-[9px] font-semibold uppercase tracking-wider bg-blue-50 text-blue-600 border border-blue-200 rounded-full px-2 py-0.5">
                      {card.badge}
                    </span>
                  </div>
                )}

                {/* Disabled lock */}
                {!card.enabled && (
                  <div className="absolute top-3 right-3">
                    <span className="text-[9px] font-medium text-gray-500 bg-gray-100 border border-gray-200 rounded-full px-2 py-0.5 flex items-center gap-1">
                      <Lock className="h-2.5 w-2.5" />
                      Coming Soon
                    </span>
                  </div>
                )}

                {/* Icon */}
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gray-100 mb-3">
                  <Icon className="h-5 w-5 text-gray-600" />
                </div>

                {/* Text */}
                <h3 className="text-sm font-semibold text-gray-900 mb-1 leading-snug">
                  {card.label}
                </h3>
                <p className="text-xs text-gray-500 leading-relaxed flex-1">
                  {card.description}
                </p>

                {/* CTA */}
                {card.enabled && (
                  <div className="flex items-center gap-1 mt-3 text-xs font-medium text-blue-600">
                    Get started <ArrowRight className="h-3.5 w-3.5" />
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
